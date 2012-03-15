# -*- coding:utf-8 -*-
# Filename:Renren.py
# 作者：华亮
#

from HTMLParser import HTMLParser
from Queue import Empty
from Queue import Queue
from re import match
from sys import exit
from urllib import urlencode
import os
import re
import socket
import threading
import time
import urllib
import urllib2
import shelve


# 提供给输出的互斥对象
GlobalPrintMutex = threading.Lock()
# 提供输出config.cfg的互斥对象
GlobalWriteConfigMutex = threading.Lock()
# 提供保存用户最后更新的互斥对象
GlobalShelveMutex = threading.Lock()


# 根据平台不同选择不同的路径分割符
Delimiter = '/' if os.name == 'posix' else '\\'

ConfigFilename = 'config.cfg'           # 每个相册的已经下载的图片id
LastUpdatedFileName = 'lastupdated.cfg' # 所有人的最后更新时间
UpdateThreashold = 10 * 60                 # 更新时间

# 多核情况下的输出
def MutexPrint(content):
    GlobalPrintMutex.acquire()
    print content
    GlobalPrintMutex.release()
    
def MutexWriteFile(file, content):
    GlobalWriteConfigMutex.acquire()
    file.write(content)
    file.flush()
    GlobalWriteConfigMutex.release()        
    
    
# 字符串形式的unicode转成真正的字符
def Str2Uni(str):
    import re
    pat = re.compile(r'\\u(\w{4})')
    lst = pat.findall(str)        
    lst.insert(0, '')
    return reduce(lambda x,y: x + unichr(int(y, 16)), lst)    

#------------------------------------------------------------------------------ 
# 下载文件的下载者
class Downloader(threading.Thread):
    def __init__(self, urlQueue, failedQueue, file=None):
        threading.Thread.__init__(self)
        self.queue = urlQueue
        self.failedQueue = failedQueue
        self.file = file  
                
    def run(self):
        try:
            while not self.queue.empty():
                pid, url, filename = self.queue.get()
                isfile = os.path.isfile(filename.decode('utf-8'))
                #print filename.decode('utf-8')
                MutexPrint(("\tDownloading %s" if not isfile else "\tExists %s") % filename.decode('utf-8'))                            
                if not isfile: urllib.urlretrieve(url, filename.decode('utf-8'))
                MutexWriteFile(self.file, pid + '\r\n')
        except Empty:
            pass
        except Exception, e:
            self.failedQueue.put(pid)
            MutexPrint('\tError occured when downloading photo which id = %s' % pid)
            MutexPrint(e)
        
           
            
    
#------------------------------------------------------------------------------ 
# 人人相册的解析
class RenrenAlbums(HTMLParser):
    in_key_div = False
    in_ul = False
    in_li = False
    in_a = False
    albumsUrl = []    
    
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and 'class' in attrs and attrs['class'] == 'big-album album-list clearfix':
            self.in_key_div = True
        elif self.in_key_div: 
            if tag == 'ul':
                self.in_ul = True
            elif self.in_ul and tag == 'li':
                self.in_li = True
            if self.in_li and tag == 'a' and 'href' in attrs:
                self.in_a = True
                self.albumsUrl.append(attrs['href'])    
                
    def handle_data(self, data):
        pass    
    
    def handle_endtag(self, tag):
        if self.in_key_div and tag == 'div':
            self.in_key_div = False
        elif self.in_ul and tag == 'ul':
            self.in_ul = False
        elif self.in_li and tag == 'li':
            self.in_li = False
        elif self.in_a and tag == 'a':
            self.in_a = False
    
    
class RenrenRequester:
    '''
    人人访问器
    '''
    LoginUrl = 'http://www.renren.com/PLogin.do'
    # 输入用户和密码的元组
    def Create(self, username, password):
        loginData = {'email':username,
                'password':password,
                'origURL':'',
                'formName':'',
                'method':'',
                'isplogin':'true',
                'submit':'登录'}
        postData = urlencode(loginData)
        cookieFile = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookieFile)
        req = urllib2.Request(self.LoginUrl, postData)
        result = self.opener.open(req)
        if not (result.geturl() == 'http://www.renren.com/home' or 'http://guide.renren.com/guide'):
            return False  
        
        rawHtml = result.read()        
        # 获取用户id
        useridPattern = re.compile(r'user : {"id" : (\d+?)}')
        self.userid = useridPattern.search(rawHtml).group(1)              
        
        # 查找requestToken        
        pos = rawHtml.find("get_check:'")
        if pos == -1: return False        
        rawHtml = rawHtml[pos + 11:]
        token = match('-\d+', rawHtml)
        if token is None:
            token = match('\d+', rawHtml)
            if token is None: return False
        self.requestToken = token.group()  
        self.__isLogin = True      
        return self.__isLogin
    
    def GetRequestToken(self):
        return self.requestToken
    
    def GetUserId(self):
        return self.userid
    
    def Request(self, url, data = None):
        if self.__isLogin:
            if data:
                encodeData = urlencode(data)
                request = urllib2.Request(url, encodeData)
            else:
                request = urllib2.Request(url)
            result = self.opener.open(request)
            return result
        else:
            return None
        
        
class RenrenPostMsg:
    '''
    RenrenPostMsg
        发布人人状态
    '''
    newStatusUrl = 'http://status.renren.com/doing/updateNew.do'
    
    def Handle(self, requester, param):
        requestToken, msg = param

        statusData = {'content':msg,
                    'isAtHome':'1',
                    'requestToken':requestToken}
        postStatusData = urlencode(statusData)
        
        requester.Request(self.newStatusUrl, statusData)
        
        return True

        
class RenrenPostGroupMsg:
    '''
    RenrenPostGroupMsg
        发布人人小组状态
    '''        
    newGroupStatusUrl = 'http://qun.renren.com/qun/ugc/create/status'
    
    def Handle(self, requester, param):
        requestToken, groupId, msg = param
        statusData = {'minigroupId':groupId,
                    'content':msg,
                    'requestToken':requestToken}
        requester.Request(self.newGroupStatusUrl, statusData)


class RenrenFriendList:
    '''
    RenrenFriendList
        人人好友列表
    '''
    def Handler(self, requester, param):     
        friendUrl = 'http://friend.renren.com/myfriendlistx.do'
        rawHtml = requester.Request(friendUrl).read()   
         
        friendInfoPack = re.search(r'var friends=\[(.*?)\];', rawHtml).group(1)        
        friendIdPattern = re.compile(r'"id":(\d+).*?"name":"(.*?)"')
        friendIdList = []
        for id, name in friendIdPattern.findall(friendInfoPack):
            friendIdList.append((id, Str2Uni(name)))
        
        return friendIdList        
    
    
class RenrenAlbumDownloader:
    '''
    AlbumDownloader
        相册下载者，记录已经下载的照片id到config.cfg，不会重新下载
    '''
    threadNumber = 10    # 下载线程数
    
    def Handler(self, requester, param):
        self.requester = requester    
        userid, path = param
        self.__DownloadOneAlbum(userid, path)
        

    # 解析html获取人名
    def __GetPeopleNameFromHtml(self, rawHtml):
        peopleNamePattern = re.compile(r'<h2>(.*?)<span>')
        # 取得人名
        peopleName = peopleNamePattern.search(rawHtml).group(1).strip()
        return peopleName
    
    def __GetAlbumsNameFromHtml(self, rawHtml):
        albumUrlPattern = re.compile(r'<a href="(.*?)" stats="album_album"><img.*?/>(.*?)</a>')
        albums = []
        # 把相册路径定向到排序页面，就可以在那个页面获得该相册下所有的相片的id
        for album_url, album_name in albumUrlPattern.findall(rawHtml):
            albums.append((album_name.strip(), album_url + '/reorder'))
        return albums
    
    def __GetAlbumPhotos(self, userid, albumUrl):
        # 匹配的正则表达式
        # 照片id
        pidPattern = re.compile(r'<li pid="(\d+)".*?>.*?</li>', re.S)        
        # 访问所有包含所有相册的页面
        result = self.requester.Request(albumUrl)
        rawHtml = result.read()
        photohtmlurl = []   # 每张照片的页面
        for pid in pidPattern.findall(rawHtml):
            photohtmlurl.append((pid, 'http://photo.renren.com/photo/%s/photo-%s' % (userid, pid)))    
            
        return photohtmlurl                 
        
    
    def __GetRealPhotoUrls(self, photohtmlurl):
        # 访问每个相册，获取所有照片，并修正相片的url
        # 照片地址
        imgPattern = re.compile(r'"largeurl":"(.*?)"')
        imgUrl = [] # id与真实照片的url
        for pid, url in photohtmlurl:
            result = self.requester.Request(url)
            rawHtml = result.read()
            for img in imgPattern.findall(rawHtml):  
                imgUrl.append((pid, img.replace('\\', '')))    
                break
                
        return imgUrl
    
    def __DownloadAlbum(self, savepath, album_name, imgUrl, file):              
        # 下载相册所有图片 
        # 将下载文件压入队列      
        queue = Queue()    
        failedQueue = Queue()  
        for pid, url in imgUrl:
            imgname = url.split('/')[-1]
            queue.put((pid, url, savepath + Delimiter + imgname))                      
        # 启动多线程下载    
        threads = []
        for i in range(self.threadNumber):
            downloader = Downloader(queue, failedQueue, file)
            threads.append(downloader)
            downloader.start()
        # 等待所有线程完成
        for t in threads:
            t.join() 
        # 返回相片队列      
        return failedQueue
            
            
    # 下载某人的相册            
    def __DownloadOneAlbum(self, userid, path='albums'):
        #if not self.__isLogin: return
        if os.path.exists(path.decode('utf-8')) == False: os.mkdir(path.decode('utf-8'))        
        
        albumsUrl = 'http://www.renren.com/profile.do?id=%s&v=photo_ajax&undefined' % userid                   
        
        try:        
            # 取出相册和路径            
            result = self.requester.Request(albumsUrl)            
            rawHtml = result.read()
            # 取得人名
            peopleName = self.__GetPeopleNameFromHtml(rawHtml).strip()
            albums = self.__GetAlbumsNameFromHtml(rawHtml)
            
            # 根据人名建文件夹
            path += Delimiter + peopleName
            if os.path.exists(path.decode('utf-8')) == False: os.mkdir(path.decode('utf-8'))          
            
            # 开始进入相册下载            
            MutexPrint('Enter %s' % peopleName.decode('utf-8'))            
            for album_name, albumUrl in albums:    
                MutexPrint('Downloading Album: %s' % album_name.decode('utf-8'))
                # 获取该相册下照片id和照片地址的表
                photohtmlurl = self.__GetAlbumPhotos(userid, albumUrl)    
                
                # 按相册名建文件夹        
                album_name = album_name.replace('\\', '')  # 消去特殊符号  
                album_name = album_name.replace('/', '')
                savepath = path + Delimiter + album_name              
                if os.path.exists(savepath.decode('utf-8')) == False: os.mkdir(savepath.decode('utf-8'))  
                
                #
                newDownloadIdSet = set()
                finishedIdSet = set()
                totalIdSet = set()
                for pid, url in photohtmlurl:
                    totalIdSet.add(pid)
                
                configFile = savepath + Delimiter + ConfigFilename
                if os.path.isfile(configFile.decode('utf-8')):  
                    # 读取已经完成的照片以免重复访问获取大图地址的页面                              
                    file = open(configFile.decode('utf-8'), 'r')                    
                    photoIdMap = []
                    for line in file.readlines():
                        pid = line.strip()
                        photoIdMap.append(pid)                        
                    file.close()                    
                    finishedIdSet = set(photoIdMap)                    
                
                newDownloadIdSet = totalIdSet - finishedIdSet
                
                newDownloadPhotoHtmlUrl = ((pid, url) for pid, url in photohtmlurl if pid in newDownloadIdSet)
                
                imgUrl = self.__GetRealPhotoUrls(newDownloadPhotoHtmlUrl)     
                #imgUrl.sort()
                #imgUrl = list(set(imgUrl)) 
               
#                for id, url in imgUrl:
#                    print id, url                           
                
                        
                # 下载照片                
                try: 
                    file = open(configFile.decode('utf-8'), 'w')
                    for id in finishedIdSet:
                        file.write(id + '\r\n')
                    file.flush()    
                    
                    failedQueue = self.__DownloadAlbum(savepath, album_name, imgUrl, file)     
                                   
                except Exception, e:
                    print 'Error when downloading.', e      
                finally:
                    # 取出下载失败的的照片的id
                    while not failedQueue.empty():
                        totalIdSet.remove(failedQueue.get())  
                    file.close()                                            
        except AttributeError, e:
            raise   
        except Exception, e:            
            print 'Error! Please contact QQ: 414112390'
            print e

    
class AutoRenrenDownloader:
    '''
    AutoRenrenDownloader
        自动下载所有好友相册，具有断点续传功能，一次下载为完成，第二次会接着下
    '''
    def handler(self, requester, param):
        self.requester = requester
        path, threadnumber = param
        self.__DownloadFriendsAlbums(path, threadnumber)
        
        
    #------------------------------------------------------------------------------ 
    # 好友相册下载者        
    class FriendDownloader(threading.Thread):
        def __init__(self, requester, queue, file):
            threading.Thread.__init__(self)
            self.file = file
            self.requester = requester
            self.queue = queue
        
        def run(self):
            try:                             
                while not self.queue.empty():
                    id, path = self.queue.get()
                    downloader = RenrenAlbumDownloader()   
                    downloader.Handler(self.requester, (id, path))
                    GlobalShelveMutex.acquire()
                    self.file['TaskList'].remove(id)
                    GlobalShelveMutex.release()
            except Empty:
                pass
            except AttributeError, e:
                print '有可能已经被人人网认为访问了100个好友，请访问人人网的任意好友的主页输入验证码'
                #print e
            except ValueError, e:
                print id
                print e
                
             
        
    def __DownloadFriendsAlbums(self, path='albums', threadnumber=10):     
        if not os.path.exists(path.decode('utf-8')): os.mkdir(path.decode('utf-8'))
        
        friendsList = RenrenFriendList().Handler(self.requester, None)
        
        db = shelve.open(LastUpdatedFileName, writeback = True)
        if not db.has_key('TaskList'): db['TaskList'] = []
        if len(db['TaskList']) == 0:
            db['TaskList'] = [id for id, realName in friendsList]
            
        updateList = db['TaskList']    
         
        i = 1
        print "此次需要更新如下："
        # 获取好友列表
        queue = Queue()
        for id in updateList:
            print "%s:\t%s\t" % (i, id),
            print dict(friendsList)[id]
            i += 1
            queue.put((id, path))
            
        # 下载好友   
        DownloadersList = []    
        failedQueue = Queue()
        try:
            for i in range(threadnumber):
                friendDownloader = self.FriendDownloader(self.requester, queue, db)
                friendDownloader.start()
                DownloadersList.append(friendDownloader)        
            for downloader in DownloadersList:
                downloader.join()
        except Exception, e:
            print '-' * 100 + "\nPlease Goto Renren.com\n" + '-' * 100 
            print e
        finally:
            db.close()
        
                   
    
        
class SuperRenren:
    '''
    SuperRenren
        人人控制器
    '''
    # 创建
    def Create(self, username, password):
        self.requester = RenrenRequester()
        if self.requester.Create(username, password):
            self.userid = self.requester.userid
            self.requestToken = self.requester.requestToken
            return True
        return False
    # 发送个人状态
    def PostMsg(self, msg):
        poster = RenrenPostMsg()
        poster.Handle(self.requester, (self.requestToken, msg))
    # 发送小组状态        
    def PostGroupMsg(self, groupId, msg):
        poster = RenrenPostGroupMsg()
        poster.Handle(self.requester, (self.requestToken, groupId, msg))
    # 下载相册
    def DownloadAlbum(self, userId, path = 'albums'):       
        downloader = RenrenAlbumDownloader()
        downloader.Handler(self.requester, (userId, path))
    # 自动下载所有好友相册
    def DownloadAllFriendsAlbums(self, path = 'albums', threadnumber = 10):
        downloader = AutoRenrenDownloader()
        downloader.handler(self.requester, (path, threadnumber))
             
        

